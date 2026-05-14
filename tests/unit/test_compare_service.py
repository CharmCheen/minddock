"""Unit tests for CompareService."""

from app.rag.retrieval_models import EvidenceFreshness, EvidenceObject
from app.rag.source_models import SourceCatalogEntry, SourceDetail, SourceState
from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk
from app.runtime.models import RuntimeResponse
from app.services.compare_service import CompareService


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.last_filters: RetrievalFilters | None = None
        self.calls: list[tuple[str, RetrievalFilters | None]] = []

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        self.last_filters = filters
        self.calls.append((query, filters))
        hits = self._hits
        if filters is not None and len(filters.sources) == 1:
            source = filters.sources[0]
            hits = [h for h in hits if h.source == source]
        return hits[:top_k]


class FakeCollection:
    """Controlled catalog for freshness tests."""

    def __init__(
        self,
        sources: dict[str, tuple[str, list[str]]],
    ) -> None:
        self._sources = sources

    def list_source_details(self, query=None):
        details = []
        for source, (doc_id, chunk_ids) in self._sources.items():
            for chunk_id in chunk_ids:
                details.append(
                    SourceDetail(
                        entry=SourceCatalogEntry(
                            doc_id=doc_id,
                            source=source,
                            source_type="file",
                            title="Test",
                            chunk_count=len(chunk_ids),
                            state=SourceState(
                                doc_id=doc_id,
                                source=source,
                                current_version="v1",
                                content_hash="v1",
                                last_ingested_at="2026-04-06T10:00:00+00:00",
                                chunk_count=len(chunk_ids),
                                ingest_status="ready",
                            ),
                        ),
                        representative_metadata={},
                    )
                )
        return details

    def list_document_chunk_ids(self, doc_id: str) -> list[str]:
        for source, (d, chunk_ids) in self._sources.items():
            if d == doc_id:
                return chunk_ids
        return []


class FreshnessAwareCollection:
    def __init__(self) -> None:
        self._details = [
            SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d1",
                    source="kb/a.md",
                    source_type="file",
                    title="A",
                    chunk_count=1,
                    state=SourceState(
                        doc_id="d1",
                        source="kb/a.md",
                        current_version="v2",
                        content_hash="v2",
                        last_ingested_at="2026-04-06T10:00:00+00:00",
                        chunk_count=1,
                        ingest_status="ready",
                    ),
                ),
                representative_metadata={},
            ),
            SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d2",
                    source="kb/b.md",
                    source_type="file",
                    title="B",
                    chunk_count=1,
                    state=SourceState(
                        doc_id="d2",
                        source="kb/b.md",
                        current_version="v2",
                        content_hash="v2",
                        last_ingested_at="2026-04-06T10:00:00+00:00",
                        chunk_count=1,
                        ingest_status="ready",
                    ),
                ),
                representative_metadata={},
            ),
        ]

    def list_source_details(self, query=None):
        return list(self._details)

    def list_document_chunk_ids(self, doc_id: str):
        return ["c1"] if doc_id == "d1" else ["c2"]


class PassthroughReranker:
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class PassthroughCompressor:
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class FakeRuntime:
    """Controlled runtime that returns a configurable JSON compare response."""

    runtime_name = "fake"
    provider_name = "fake-provider"

    def __init__(self, text: str = "", used_fallback: bool = False, raise_on_generate: bool = False):
        self._text = text
        self._used_fallback = used_fallback
        self._raise = raise_on_generate

    def generate(self, request):
        if self._raise:
            raise RuntimeError("Runtime failure")
        return RuntimeResponse(
            text=self._text,
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
            used_fallback=self._used_fallback,
        )


def _make_service(*, hits, runtime=None, collection=None):
    """Helper to build a CompareService with controlled dependencies."""
    return CompareService(
        search_service=FakeSearchService(hits),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime or FakeRuntime(),
        collection=collection,
    )


def test_compare_returns_differences_with_evidence() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A stores data in local Chroma for offline retrieval.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
                extra_metadata={"source_version": "v1", "content_hash": "v1"},
            ),
            RetrievedChunk(
                text="Project B stores data in Postgres for synchronized access.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
                extra_metadata={"source_version": "v1", "content_hash": "v1"},
            ),
        ],
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(
        question="How do the systems store data?",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )

    assert result.compare_result.support_status.value == "supported"
    assert result.compare_result.differences
    point = result.compare_result.differences[0]
    assert point.left_evidence[0].chunk_id == "c1"
    assert point.right_evidence[0].chunk_id == "c2"
    assert point.left_evidence[0].freshness.value == "fresh"
    assert point.right_evidence[0].freshness.value == "fresh"


def test_compare_returns_common_points_with_evidence() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Doc A explains authentication tokens for API requests.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Doc A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Doc B also explains authentication tokens for client API requests.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Doc B",
                distance=0.25,
            ),
        ],
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="How is authentication handled?", top_k=4)

    assert result.compare_result.common_points
    point = result.compare_result.common_points[0]
    assert point.left_evidence
    assert point.right_evidence
    # Statement should reference shared content terms, not restate the question
    assert "how is authentication handled" not in point.statement.lower()


def test_compare_returns_insufficient_evidence_when_only_one_side_is_available() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Only one document discusses the topic.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/only.md",
                distance=0.2,
            )
        ],
    )

    result = service.compare(question="Compare the documents", top_k=3)

    assert result.compare_result.support_status.value == "insufficient_evidence"
    assert result.compare_result.refusal_reason is not None
    assert result.compare_result.refusal_reason.value == "insufficient_context"
    assert result.metadata.insufficient_evidence is True
    assert result.compare_result.common_points == ()
    assert result.compare_result.differences == ()
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["operation"] == "compare"
    assert trace["final_citation_count"] == 0
    assert trace["final_evidence_count"] == 0
    assert "no_citations" in trace["trace_warnings"]
    assert "insufficient_context" in trace["trace_warnings"]


def test_compare_refreshes_freshness_before_returning() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A stores data in local Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
                extra_metadata={"source_version": "v1", "content_hash": "v1"},
            ),
            RetrievedChunk(
                text="Project B stores data in Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
                extra_metadata={"source_version": "v2", "content_hash": "v2"},
            ),
        ],
        collection=FreshnessAwareCollection(),
    )

    result = service.compare(question="How do the systems store data?", top_k=4)

    point = result.compare_result.differences[0]
    assert point.left_evidence[0].freshness == EvidenceFreshness.STALE_POSSIBLE
    assert point.right_evidence[0].freshness == EvidenceFreshness.FRESH


# ---------------------------------------------------------------------------
# LLM-backed compare tests
# ---------------------------------------------------------------------------


def test_compare_uses_llm_json_when_valid() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","summary_note":"Shared storage pattern.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":['
        '{"statement":"Different backends.","summary_note":"A uses Chroma, B uses Postgres.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.compare_result.common_points
    assert result.compare_result.differences
    assert result.compare_result.common_points[0].statement == "Both use vector stores."
    assert result.compare_result.differences[0].statement == "Different backends."


def test_compare_llm_evidence_ids_map_correctly() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R2"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Left hit 2",
                doc_id="d1",
                chunk_id="c2",
                source="kb/a.md",
                distance=0.15,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c3",
                source="kb/b.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Right hit 2",
                doc_id="d2",
                chunk_id="c4",
                source="kb/b.md",
                distance=0.25,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1", "c2"]), "kb/b.md": ("d2", ["c3", "c4"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    assert point.left_evidence[0].chunk_id == "c1"
    assert point.right_evidence[0].chunk_id == "c4"


def test_compare_falls_back_to_heuristic_on_json_parse_failure() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text="not valid json"),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    # Heuristic should produce evidence-based points, not template
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"
    all_statements = [
        p.statement
        for p in (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    ]
    for stmt in all_statements:
        assert "Both sources contain evidence relevant to" not in stmt
        assert "emphasize different details" not in stmt
        assert "requested topic" not in stmt


def test_compare_falls_back_to_heuristic_when_runtime_raises() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_falls_back_to_heuristic_on_empty_llm_arrays() -> None:
    llm_json = '{"common_points":[],"differences":[],"conflicts":[]}'
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_fallback_preserves_citations() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.citations
    doc_ids = {c.doc_id for c in result.citations}
    assert "d1" in doc_ids
    assert "d2" in doc_ids


def test_compare_llm_path_preserves_grounded_compare_result_fields() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","summary_note":"Shared storage pattern.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":['
        '{"statement":"Different backends.","summary_note":"A uses Chroma, B uses Postgres.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.compare_result.query == "Compare storage"
    assert result.compare_result.support_status.value == "supported"
    assert result.compare_result.refusal_reason is None
    assert result.compare_result.common_points[0].left_evidence
    assert result.compare_result.common_points[0].right_evidence
    assert result.compare_result.common_points[0].summary_note == "Shared storage pattern."


def test_compare_llm_invalid_left_id_uses_top_evidence_fallback() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":"note","left_evidence_ids":["L99"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    assert point.left_evidence
    assert point.right_evidence
    assert point.left_evidence[0].chunk_id == "c1"


def test_compare_llm_invalid_right_id_uses_top_evidence_fallback() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R99"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    assert point.left_evidence
    assert point.right_evidence
    assert point.right_evidence[0].chunk_id == "c2"


def test_compare_llm_both_ids_invalid_uses_top_evidence_fallback() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":"note","left_evidence_ids":["L99"],"right_evidence_ids":["R99"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    assert point.left_evidence[0].chunk_id == "c1"
    assert point.right_evidence[0].chunk_id == "c2"


def test_compare_llm_statement_dict_skips_point_and_fallback_if_empty() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":{"bad":"dict"},"summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left document discusses caching strategies for web applications.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right document discusses load balancing strategies for web servers.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    # All LLM points discarded -> fallback to heuristic
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_llm_evidence_ids_string_not_parsed_char_by_char() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":"note","left_evidence_ids":"L1","right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    # left_evidence_ids was a string, treated as invalid -> fallback to top evidence
    assert point.left_evidence[0].chunk_id == "c1"
    assert point.right_evidence[0].chunk_id == "c2"


def test_compare_llm_missing_common_points_key_fallback_heuristic() -> None:
    llm_json = '{"differences":[],"conflicts":[]}'
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left discusses vector search algorithms and indexing.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right discusses vector search algorithms and retrieval.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    # Missing required key -> fallback heuristic
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_llm_differences_not_list_fallback_heuristic() -> None:
    llm_json = '{"common_points":[],"differences":"not a list","conflicts":[]}'
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left discusses vector search algorithms and indexing.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right discusses vector search algorithms and retrieval.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    # differences not a list -> fallback heuristic
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_llm_summary_note_dict_treated_as_none() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Common topic.","summary_note":{"bad":"dict"},"left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    point = result.compare_result.common_points[0]
    assert point.statement == "Common topic."
    assert point.summary_note is None
    assert point.left_evidence[0].chunk_id == "c1"
    assert point.right_evidence[0].chunk_id == "c2"


def test_compare_llm_json_fenced_with_json_tag() -> None:
    llm_json = (
        '```json\n'
        '{"common_points":['
        '{"statement":"Fenced json.","summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}\n'
        '```'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    assert result.compare_result.common_points[0].statement == "Fenced json."


def test_compare_llm_json_fenced_with_plain_fence() -> None:
    llm_json = (
        '```\n'
        '{"common_points":['
        '{"statement":"Plain fence.","summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}\n'
        '```'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    assert result.compare_result.common_points[0].statement == "Plain fence."


def test_compare_llm_used_fallback_with_valid_json_parses_successfully() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Fallback but valid.","summary_note":"note","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left hit 1",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right hit 1",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text=llm_json, used_fallback=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    assert result.compare_result.common_points[0].statement == "Fallback but valid."


def test_compare_llm_used_fallback_with_invalid_json_fallback_heuristic() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Left discusses vector search algorithms and indexing.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.1,
            ),
            RetrievedChunk(
                text="Right discusses vector search algorithms and retrieval.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.2,
            ),
        ],
        runtime=FakeRuntime(text="not json", used_fallback=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    # Invalid JSON even with used_fallback=True -> fallback heuristic
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


# ---------------------------------------------------------------------------
# Source-scoped compare tests (Phase 6B)
# ---------------------------------------------------------------------------


def test_two_selected_sources_triggers_separate_retrieval_calls() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="B uses Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )
    assert len(service.search_service.calls) == 2
    assert service.search_service.calls[0][1].sources == ("kb/a.md",)
    assert service.search_service.calls[1][1].sources == ("kb/b.md",)
    assert result.compare_result.support_status.value == "supported"


def test_two_selected_sources_preserves_non_source_filters() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="B uses Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md"), section="intro"),
    )
    assert len(service.search_service.calls) == 2
    for _query, filters in service.search_service.calls:
        assert filters.section == "intro"


def test_two_selected_sources_result_contains_evidence_from_both() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A implements Chroma vector database for local storage and retrieval.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B implements Postgres relational database for remote storage and queries.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )
    assert result.compare_result.support_status.value == "supported"
    all_points = (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    assert all_points, "At least one comparison point expected"
    point = all_points[0]
    assert point.left_evidence[0].source == "kb/a.md"
    assert point.right_evidence[0].source == "kb/b.md"


def test_two_selected_sources_one_empty_returns_insufficient() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )
    assert result.compare_result.support_status.value == "insufficient_evidence"
    assert result.metadata.insufficient_evidence is True


def test_more_than_two_selected_sources_uses_first_two_and_warns() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="B uses Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
            RetrievedChunk(
                text="C uses Redis.",
                doc_id="d3",
                chunk_id="c3",
                source="kb/c.md",
                distance=0.4,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md", "kb/c.md")),
    )
    assert len(service.search_service.calls) == 2
    assert result.compare_result.support_status.value == "supported"
    assert any("two sources" in w for w in result.metadata.warnings)
    assert any(issue.code == "compare_source_limit" for issue in result.metadata.issues)
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert trace["operation"] == "compare"
    assert trace["has_explicit_source_filter"] is True
    assert trace["selected_sources_count"] == 3
    assert trace["selected_sources_preview"] == ["kb/a.md", "kb/b.md", "kb/c.md"]
    assert trace["final_citation_count"] >= 0
    assert any("two sources" in w for w in trace["trace_warnings"])
    assert "retry_count" not in trace
    assert "max_retries" not in trace
    assert "quality_reasons" not in trace
    assert "low_confidence" not in trace


def test_no_selected_sources_keeps_single_retrieval() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="B uses Postgres.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
    )
    assert len(service.search_service.calls) == 1
    assert result.compare_result.support_status.value == "supported"


def test_llm_path_works_with_two_selected_sources() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","summary_note":"Shared storage pattern.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":['
        '{"statement":"Different backends.","summary_note":"A uses Chroma, B uses Postgres.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )
    assert result.compare_result.common_points
    assert result.compare_result.differences
    assert result.compare_result.common_points[0].statement == "Both use vector stores."
    assert result.compare_result.differences[0].statement == "Different backends."


def test_heuristic_fallback_works_with_two_selected_sources() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md")),
    )
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_more_than_two_selected_sources_insufficient_preserves_source_limit_warning() -> None:
    """When >2 sources are selected but only one has evidence,
    the source limit warning still appears in metadata and issues."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="A uses Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
        ],
        collection=FakeCollection(sources={}),
    )
    result = service.compare(
        question="Compare storage",
        top_k=4,
        filters=RetrievalFilters(sources=("kb/a.md", "kb/b.md", "kb/c.md")),
    )
    assert result.compare_result.support_status.value == "insufficient_evidence"
    assert result.metadata.insufficient_evidence is True
    assert any("two sources" in w for w in result.metadata.warnings)
    assert any("Insufficient grounded evidence" in w for w in result.metadata.warnings)
    assert any(issue.code == "compare_source_limit" for issue in result.metadata.issues)
    assert any(issue.code == "insufficient_evidence" for issue in result.metadata.issues)
    trace = result.metadata.workflow_trace
    assert trace is not None
    assert any("two sources" in w for w in trace["trace_warnings"])


# ---------------------------------------------------------------------------
# Compare 2.0 optional metadata tests
# ---------------------------------------------------------------------------


def test_llm_json_with_confidence_parses_correctly() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","confidence":0.85,"left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.common_points[0]
    assert point.confidence == 0.85


def test_llm_json_with_taxonomy_parses_correctly() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","taxonomy":"method","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.common_points[0]
    assert point.taxonomy == "method"


def test_llm_json_missing_confidence_and_taxonomy_backward_compatible() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.common_points[0]
    assert point.confidence is None
    assert point.taxonomy is None
    assert point.evidence_coverage is not None


def test_llm_json_invalid_confidence_becomes_none() -> None:
    llm_json = (
        '{"common_points":['
        '{"statement":"Both use vector stores.","confidence":"not_a_number","left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}'
        '],"differences":[],"conflicts":[]}'
    )
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector store.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector store.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.common_points[0]
    assert point.confidence is None


def test_clamp_confidence_below_zero_clamps_to_zero() -> None:
    service = _make_service(hits=[])
    assert service._clamp_confidence(-0.5) == 0.0


def test_clamp_confidence_above_one_clamps_to_one() -> None:
    service = _make_service(hits=[])
    assert service._clamp_confidence(1.5) == 1.0


def test_normalize_taxonomy_unknown_becomes_other() -> None:
    service = _make_service(hits=[])
    assert service._normalize_taxonomy("unknown_category") == "other"


def test_evidence_coverage_balanced_when_counts_match() -> None:
    service = _make_service(hits=[])
    left = (EvidenceObject(doc_id="d1", chunk_id="c1", source="a.md", snippet="s1"),)
    right = (EvidenceObject(doc_id="d2", chunk_id="c2", source="b.md", snippet="s2"),)
    coverage = service._compute_evidence_coverage(left, right)
    assert coverage["left_count"] == 1
    assert coverage["right_count"] == 1
    assert coverage["balanced"] is True
    assert coverage["coverage_label"] == "balanced"


def test_evidence_coverage_left_heavy_when_left_greater() -> None:
    service = _make_service(hits=[])
    left = (
        EvidenceObject(doc_id="d1", chunk_id="c1", source="a.md", snippet="s1"),
        EvidenceObject(doc_id="d1", chunk_id="c2", source="a.md", snippet="s2"),
    )
    right = (EvidenceObject(doc_id="d2", chunk_id="c3", source="b.md", snippet="s3"),)
    coverage = service._compute_evidence_coverage(left, right)
    assert coverage["coverage_label"] == "left_heavy"


def test_evidence_coverage_right_heavy_when_right_greater() -> None:
    service = _make_service(hits=[])
    left = (EvidenceObject(doc_id="d1", chunk_id="c1", source="a.md", snippet="s1"),)
    right = (
        EvidenceObject(doc_id="d2", chunk_id="c2", source="b.md", snippet="s2"),
        EvidenceObject(doc_id="d2", chunk_id="c3", source="b.md", snippet="s3"),
    )
    coverage = service._compute_evidence_coverage(left, right)
    assert coverage["coverage_label"] == "right_heavy"


def test_heuristic_fallback_sets_confidence_none() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.differences[0]
    assert point.confidence is None
    assert point.taxonomy is None


def test_heuristic_fallback_computes_evidence_coverage() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    point = result.compare_result.differences[0]
    assert point.evidence_coverage is not None
    assert point.evidence_coverage["left_count"] == 1
    assert point.evidence_coverage["right_count"] == 1
    assert point.evidence_coverage["coverage_label"] == "balanced"


def test_existing_json_parse_failure_fallback_still_works() -> None:
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A uses Chroma vector database for storage.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B uses Postgres vector database for storage.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text="not valid json"),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )
    result = service.compare(question="Compare storage", top_k=4)
    assert result.compare_result.differences or result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"
    point = result.compare_result.differences[0]
    assert point.confidence is None
    assert point.evidence_coverage is not None


# ---------------------------------------------------------------------------
# Regression: model refusal detection in compare (Bug B)
# ---------------------------------------------------------------------------


def test_compare_detects_model_refusal_and_returns_insufficient() -> None:
    """When the LLM returns refusal text, compare should return INSUFFICIENT_EVIDENCE."""
    refusal_text = "证据不足，无法从提供的证据中进行对比。"
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Some unrelated content about weather.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Doc A",
                distance=0.5,
            ),
            RetrievedChunk(
                text="Another unrelated content about cooking.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Doc B",
                distance=0.6,
            ),
        ],
        runtime=FakeRuntime(text=refusal_text),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare the two documents", top_k=4)

    assert result.compare_result.support_status.value == "insufficient_evidence"
    assert result.compare_result.refusal_reason.value == "model_refused"
    assert not result.citations
    assert result.metadata.insufficient_evidence is True
    assert result.metadata.timing.generation_ms is not None


# ---------------------------------------------------------------------------
# Heuristic fallback quality regression tests
# ---------------------------------------------------------------------------


def test_heuristic_fallback_does_not_restate_question() -> None:
    """Heuristic fallback must not embed the user question in any point statement."""
    question = "Compare the research directions of these two papers"
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Paper A focuses on neural architecture search for vision tasks.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Paper A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Paper B focuses on reinforcement learning for robotics control.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Paper B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question=question, top_k=4)

    all_statements = [
        p.statement.lower()
        for p in (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    ]
    for stmt in all_statements:
        assert question.lower() not in stmt, f"Statement restates question: {stmt}"


def test_heuristic_fallback_does_not_use_template_phrases() -> None:
    """Heuristic fallback must not produce banned template phrases."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="System A implements distributed consensus using Raft protocol.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="System A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="System B implements distributed consensus using Paxos protocol.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="System B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare the systems", top_k=4)

    banned = [
        "both sources contain evidence relevant to",
        "emphasize different details",
        "requested topic",
    ]
    all_statements = [
        p.statement.lower()
        for p in (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    ]
    for stmt in all_statements:
        for phrase in banned:
            assert phrase not in stmt, f"Statement contains banned phrase '{phrase}': {stmt}"


def test_heuristic_fallback_invalid_json_produces_evidence_based_or_insufficient() -> None:
    """When LLM returns invalid JSON, heuristic should produce evidence-based
    differences or return insufficient_evidence — never template garbage."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="This paper proposes a novel transformer architecture for NLP tasks.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Paper A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="This paper evaluates convolutional networks on image classification benchmarks.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Paper B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text="not valid json at all"),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare approaches", top_k=4)

    all_points = (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    if all_points:
        for point in all_points:
            assert "both sources contain evidence" not in point.statement.lower()
            assert "emphasize different details" not in point.statement.lower()
            # Must have evidence on both sides
            assert point.left_evidence
            assert point.right_evidence
    else:
        # No points generated is acceptable — honest degradation
        assert result.compare_result.support_status.value == "insufficient_evidence"


def test_heuristic_fallback_empty_evidence_groups_returns_insufficient() -> None:
    """When evidence is genuinely insufficient, heuristic should not fabricate points."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="X",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Y",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text='{"common_points":[],"differences":[],"conflicts":[]}'),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare X and Y", top_k=4)

    # Minimal evidence with no overlap and no meaningful difference
    # Either heuristic finds a difference or system reports insufficient
    if not result.compare_result.differences and not result.compare_result.common_points:
        assert result.compare_result.support_status.value == "insufficient_evidence"


def test_compare_v1_structure_preserved_after_fallback() -> None:
    """compare.v1 artifact structure must be preserved even after heuristic fallback."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Module A handles authentication via JWT tokens.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Module A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Module B handles authentication via session cookies.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Module B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(text="invalid json"),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare auth", top_k=4)

    # Structure fields must exist
    assert hasattr(result.compare_result, "common_points")
    assert hasattr(result.compare_result, "differences")
    assert hasattr(result.compare_result, "conflicts")
    assert hasattr(result.compare_result, "support_status")
    assert hasattr(result.compare_result, "query")
    assert result.compare_result.query == "Compare auth"

    # API dict must have the expected keys
    api = result.compare_result.to_api_dict()
    assert "common_points" in api
    assert "differences" in api
    assert "conflicts" in api
    assert "support_status" in api


def test_heuristic_fallback_evidence_ids_bind_correctly() -> None:
    """Evidence/citation IDs must still bind after heuristic fallback."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Project A implements caching with Redis for performance.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Project A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Project B implements caching with Memcached for performance.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Project B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare caching", top_k=4)

    assert result.citations
    doc_ids = {c.doc_id for c in result.citations}
    assert "d1" in doc_ids
    assert "d2" in doc_ids

    all_points = (*result.compare_result.common_points, *result.compare_result.differences, *result.compare_result.conflicts)
    for point in all_points:
        assert point.left_evidence, "left_evidence must not be empty"
        assert point.right_evidence, "right_evidence must not be empty"
        assert point.left_evidence[0].chunk_id == "c1"
        assert point.right_evidence[0].chunk_id == "c2"


# ---------------------------------------------------------------------------
# Quality gate: generic term filtering and minimum evidence threshold
# ---------------------------------------------------------------------------


def test_common_term_extraction_filters_generic_terms() -> None:
    """_extract_common_terms should not return generic/domain-neutral words."""
    from app.services.compare_service import CompareService

    # These texts share only generic terms: research, model, system, method, data
    left = "The research model uses a novel system method for data processing."
    right = "The research model proposes a different system method for data analysis."
    terms = CompareService._extract_common_terms(left, right)
    generic = {"research", "model", "system", "method", "data", "paper", "study", "approach", "result", "analysis"}
    for term in terms:
        assert term not in generic, f"Generic term leaked through: {term}"


def test_generic_only_overlap_does_not_produce_common_points() -> None:
    """When evidence texts share only generic terms, common_points should be empty."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="The research model uses a system method for data.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Paper A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="The research model proposes a system method for data.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Paper B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare approaches", top_k=4)

    # Only generic overlap → no common_points
    assert result.compare_result.common_points == ()


def test_specific_overlap_still_produces_common_points() -> None:
    """When evidence texts share specific domain terms, common_points should appear."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Both papers use transformer attention mechanism for encoding.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Paper A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Both papers use transformer attention mechanism for decoding.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Paper B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare models", top_k=4)

    # Specific terms: transformer, attention, mechanism
    assert result.compare_result.common_points
    stmt = result.compare_result.common_points[0].statement.lower()
    assert "overlapping topics" in stmt


def test_very_short_evidence_does_not_produce_difference() -> None:
    """Evidence with fewer than 5 tokens should not generate a difference statement."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="short",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="A",
                distance=0.2,
            ),
            RetrievedChunk(
                text="brief",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="B",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare X", top_k=4)

    # Both snippets under 5 tokens → no difference, no common → insufficient
    assert result.compare_result.differences == ()
    assert result.compare_result.common_points == ()
    assert result.compare_result.support_status.value == "insufficient_evidence"


def test_borderline_evidence_with_five_tokens_produces_difference() -> None:
    """Evidence with exactly 5 tokens should be allowed to produce a difference."""
    service = _make_service(
        hits=[
            RetrievedChunk(
                text="Alpha focuses on neural network training.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/a.md",
                title="Alpha",
                distance=0.2,
            ),
            RetrievedChunk(
                text="Beta focuses on distributed systems architecture design.",
                doc_id="d2",
                chunk_id="c2",
                source="kb/b.md",
                title="Beta",
                distance=0.3,
            ),
        ],
        runtime=FakeRuntime(raise_on_generate=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare", top_k=4)

    # Both have >= 5 tokens, no generic-only overlap → difference should appear
    assert result.compare_result.differences
    assert "different focuses" in result.compare_result.differences[0].statement.lower()
