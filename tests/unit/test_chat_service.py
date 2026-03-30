"""Unit tests for ChatService."""

from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.services.chat_service import ChatService


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
    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        return f"answer for {query} with {len(evidence)} evidence"


def test_chat_returns_insufficient_evidence_when_no_grounded_hits() -> None:
    service = ChatService(
        search_service=FakeSearchService(
            [
                {
                    "text": "weak",
                    "doc_id": "d1",
                    "chunk_id": "c1",
                    "source": "doc.md",
                    "distance": 9.9,
                }
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        llm=FakeLLM(),
    )

    result = service.chat(query="test", top_k=3)

    assert result["answer"] == INSUFFICIENT_EVIDENCE
    assert result["citations"] == []
    assert result["retrieved_count"] == 0


def test_chat_returns_answer_and_citations_for_grounded_hits() -> None:
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
    service = ChatService(
        search_service=search_service,
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        llm=FakeLLM(),
    )

    result = service.chat(
        query="where is data stored",
        top_k=3,
        filters={"source": "kb/doc.md", "section": "Storage"},
    )

    assert result["answer"] == "answer for where is data stored with 1 evidence"
    assert result["retrieved_count"] == 1
    assert result["citations"][0]["chunk_id"] == "c1"
    assert result["citations"][0]["source"] == "kb/doc.md"
    assert result["citations"][0]["section"] == "Storage"
    assert result["citations"][0]["location"] == "Storage"
    assert result["citations"][0]["ref"] == "doc > Storage"
    assert result["citations"][0]["page"] is None
    assert result["citations"][0]["anchor"] is None
    assert search_service.last_filters == {"source": "kb/doc.md", "section": "Storage"}
