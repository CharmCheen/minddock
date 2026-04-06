"""Unit tests for CompareService."""

from app.rag.retrieval_models import RetrievalFilters, RetrievedChunk
from app.services.compare_service import CompareService


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


def test_compare_returns_differences_with_evidence() -> None:
    service = CompareService(
        search_service=FakeSearchService(
            [
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
                    extra_metadata={"source_version": "v2", "content_hash": "v2"},
                ),
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
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
    service = CompareService(
        search_service=FakeSearchService(
            [
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
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
    )

    result = service.compare(question="How is authentication handled?", top_k=4)

    assert result.compare_result.common_points
    point = result.compare_result.common_points[0]
    assert point.left_evidence
    assert point.right_evidence
    assert "authentication" in point.statement.lower() or "relevant" in point.statement.lower()


def test_compare_returns_insufficient_evidence_when_only_one_side_is_available() -> None:
    service = CompareService(
        search_service=FakeSearchService(
            [
                RetrievedChunk(
                    text="Only one document discusses the topic.",
                    doc_id="d1",
                    chunk_id="c1",
                    source="kb/only.md",
                    distance=0.2,
                )
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
    )

    result = service.compare(question="Compare the documents", top_k=3)

    assert result.compare_result.support_status.value == "insufficient_evidence"
    assert result.compare_result.refusal_reason is not None
    assert result.compare_result.refusal_reason.value == "insufficient_context"
    assert result.metadata.insufficient_evidence is True
    assert result.compare_result.common_points == ()
    assert result.compare_result.differences == ()
