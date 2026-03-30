"""Unit tests for SummarizeService."""

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.services.summarize_service import SummarizeService


class FakeSearchService:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self._hits = hits
        self.last_filters: dict[str, str] | None = None

    def retrieve(self, query: str, top_k: int, filters: dict[str, str] | None = None) -> list[dict[str, object]]:
        self.last_filters = filters
        return self._hits[:top_k]


class PassthroughReranker:
    def rerank(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        return hits


class PassthroughCompressor:
    def compress(self, query: str, hits: list[dict[str, object]]) -> list[dict[str, object]]:
        return hits


class FakeLLM:
    def __init__(self) -> None:
        self.last_query = ""
        self.last_evidence: list[dict[str, object]] = []

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        self.last_query = query
        self.last_evidence = evidence
        return f"summary for {len(evidence)} evidence"


def test_summarize_returns_summary_and_citations() -> None:
    search_service = FakeSearchService(
        [
            {
                "text": "MindDock stores chunks in Chroma.",
                "doc_id": "d1",
                "chunk_id": "c1",
                "source": "kb/doc.md",
                "title": "doc",
                "section": "Storage",
                "location": "Storage",
                "ref": "doc > Storage",
                "page": None,
                "anchor": None,
                "distance": 0.2,
            }
        ]
    )
    llm = FakeLLM()
    service = SummarizeService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        llm=llm,
    )

    result = service.summarize(
        topic="storage design",
        top_k=3,
        filters={"source": "kb/doc.md", "section": "Storage"},
    )

    assert result["summary"] == "summary for 1 evidence"
    assert result["retrieved_count"] == 1
    assert result["citations"][0]["ref"] == "doc > Storage"
    assert result["citations"][0]["page"] is None
    assert result["citations"][0]["anchor"] is None
    assert search_service.last_filters == {"source": "kb/doc.md", "section": "Storage"}
    assert "Summarize the topic" in llm.last_query
    assert "storage design" in llm.last_query


def test_summarize_returns_insufficient_evidence_when_no_hits() -> None:
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        llm=FakeLLM(),
    )

    result = service.summarize(topic="empty", top_k=3)

    assert result["summary"] == INSUFFICIENT_EVIDENCE
    assert result["citations"] == []
    assert result["retrieved_count"] == 0
