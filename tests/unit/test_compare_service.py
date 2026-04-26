"""Unit tests for CompareService."""

from app.rag.retrieval_models import EvidenceFreshness
from app.rag.source_models import SourceCatalogEntry, SourceDetail, SourceState
from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk
from app.runtime.models import RuntimeResponse
from app.services.compare_service import CompareService


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.last_filters: RetrievalFilters | None = None

    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        self.last_filters = filters
        return self._hits[:top_k]


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
    assert "authentication" in point.statement.lower() or "relevant" in point.statement.lower()


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
        runtime=FakeRuntime(text="not valid json"),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    # Heuristic should produce at least a common_points entry
    assert result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_falls_back_to_heuristic_when_runtime_raises() -> None:
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

    assert result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_falls_back_to_heuristic_on_empty_llm_arrays() -> None:
    llm_json = '{"common_points":[],"differences":[],"conflicts":[]}'
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
        runtime=FakeRuntime(text=llm_json),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare storage", top_k=4)

    assert result.compare_result.common_points
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

    # All LLM points discarded -> fallback to heuristic
    assert result.compare_result.common_points
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

    # Missing required key -> fallback heuristic
    assert result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"


def test_compare_llm_differences_not_list_fallback_heuristic() -> None:
    llm_json = '{"common_points":[],"differences":"not a list","conflicts":[]}'
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

    # differences not a list -> fallback heuristic
    assert result.compare_result.common_points
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
        runtime=FakeRuntime(text="not json", used_fallback=True),
        collection=FakeCollection(sources={"kb/a.md": ("d1", ["c1"]), "kb/b.md": ("d2", ["c2"])}),
    )

    result = service.compare(question="Compare docs", top_k=4)

    # Invalid JSON even with used_fallback=True -> fallback heuristic
    assert result.compare_result.common_points
    assert result.compare_result.support_status.value == "supported"
