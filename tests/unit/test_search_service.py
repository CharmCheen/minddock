"""Unit tests for SearchService."""

from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.services.search_service import SearchService
from app.services.service_models import SearchServiceResult


class FakeVectorStore:
    def __init__(self) -> None:
        self.last_query = ""
        self.last_top_k = 0
        self.last_filters: RetrievalFilters | None = None

    def search_by_text(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        self.last_query = query
        self.last_top_k = top_k
        self.last_filters = filters
        return [
            RetrievedChunk(
                text="filtered result",
                doc_id="d1",
                chunk_id="c1",
                source="kb/allowed.md",
                source_type="file",
                section="Storage",
                location="Storage",
                ref="allowed > Storage",
                title="allowed",
                distance=0.1,
            )
        ]


class EmptyVectorStore:
    def search_by_text(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        return []


class FakeHybridService:
    def __init__(self, hits: list[RetrievedChunk], fail: bool = False) -> None:
        self.hits = hits
        self.fail = fail
        self.last_query = ""
        self.last_top_k = 0
        self.last_filters: RetrievalFilters | None = None

    def retrieve_lexical_candidates(
        self,
        query: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        self.last_query = query
        self.last_top_k = top_k
        self.last_filters = filters
        if self.fail:
            raise RuntimeError("bm25 unavailable")
        return self.hits[:top_k]


def test_search_service_uses_vectorstore_path() -> None:
    vectorstore = FakeVectorStore()
    service = SearchService(vectorstore=vectorstore)

    result = service.search(
        query="where is data stored",
        top_k=2,
        filters=RetrievalFilters(sources=("kb/allowed.md",), section="Storage"),
    )

    assert vectorstore.last_query == "where is data stored"
    assert vectorstore.last_top_k == 2
    assert vectorstore.last_filters == RetrievalFilters(sources=("kb/allowed.md",), section="Storage")
    assert isinstance(result, SearchServiceResult)
    assert result.metadata.retrieved_count == 1
    assert result.search_result.to_api_dict()["hits"][0]["source"] == "kb/allowed.md"
    assert result.search_result.to_api_dict()["hits"][0]["citation"]["source"] == "kb/allowed.md"


def test_search_returns_citation_per_hit() -> None:
    service = SearchService(vectorstore=FakeVectorStore())
    result = service.search(query="test", top_k=1).search_result.to_api_dict()

    hit = result["hits"][0]
    citation = hit["citation"]
    assert citation["doc_id"] == "d1"
    assert citation["chunk_id"] == "c1"
    assert citation["source"] == "kb/allowed.md"
    assert citation["page"] is None
    assert citation["anchor"] is None
    assert citation["title"] == "allowed"
    assert citation["section"] == "Storage"


def test_search_hit_still_has_text_and_distance() -> None:
    service = SearchService(vectorstore=FakeVectorStore())
    result = service.search(query="test", top_k=1).search_result.to_api_dict()

    hit = result["hits"][0]
    assert hit["text"] == "filtered result"
    assert hit["distance"] == 0.1


def test_search_empty_result_sets_metadata() -> None:
    result = SearchService(vectorstore=EmptyVectorStore()).search(query="missing", top_k=1)
    assert result.metadata.empty_result is True
    assert result.metadata.warnings
    assert result.metadata.issues[0].code == "empty_result"


def test_search_service_returns_structured_reference_lexical_candidates() -> None:
    hit = RetrievedChunk(
        text="Table 1 highlights differences.",
        doc_id="d1",
        chunk_id="table1",
        source="paper.pdf",
    )
    hybrid_service = FakeHybridService([hit])
    service = SearchService(vectorstore=FakeVectorStore(), hybrid_service=hybrid_service)
    filters = RetrievalFilters(sources=("paper.pdf",))

    result = service.retrieve_structured_reference_candidates(
        query="What does Table 1 summarize?",
        top_k=5,
        filters=filters,
    )

    assert result == [hit]
    assert hybrid_service.last_query == "What does Table 1 summarize?"
    assert hybrid_service.last_top_k == 5
    assert hybrid_service.last_filters == filters


def test_search_service_structured_reference_candidates_fallback_on_bm25_error() -> None:
    service = SearchService(
        vectorstore=FakeVectorStore(),
        hybrid_service=FakeHybridService([], fail=True),
    )

    assert service.retrieve_structured_reference_candidates("Table 1", top_k=5) == []
