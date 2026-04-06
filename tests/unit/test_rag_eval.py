"""Unit tests for lightweight evaluation helpers."""

from app.eval.rag_eval import EvalCase, evaluate_cases
from app.rag.retrieval_models import CitationRecord, RetrievedChunk, SearchHitRecord, SearchResult
from app.services.service_models import SearchServiceResult, SummarizeServiceResult, UseCaseMetadata


class FakeSearchService:
    def search(self, query: str, top_k: int) -> SearchServiceResult:
        chunk = RetrievedChunk(text="text", doc_id="d1", chunk_id="c1", source="example.md")
        return SearchServiceResult(
            search_result=SearchResult(
                query=query,
                top_k=top_k,
                hits=[
                    SearchHitRecord(
                        chunk=chunk,
                        citation=CitationRecord(doc_id="d1", chunk_id="c1", source="example.md", snippet="text"),
                    )
                ],
            ),
            metadata=UseCaseMetadata(retrieved_count=1),
        )


class FakeSummarizeService:
    def summarize(self, topic: str, top_k: int) -> SummarizeServiceResult:
        return SummarizeServiceResult(
            summary="summary",
            citations=[CitationRecord(doc_id="d1", chunk_id="c1", source="example.md", snippet="text")],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="text"),
            structured_output=None,
        )


def test_evaluate_cases_returns_summary(monkeypatch) -> None:
    monkeypatch.setattr("app.eval.rag_eval.SearchService", lambda: FakeSearchService())
    monkeypatch.setattr("app.eval.rag_eval.SummarizeService", lambda: FakeSummarizeService())

    report = evaluate_cases([EvalCase(query="storage", expected_source="example.md")])

    assert report["summary"]["top_hit_rate"] == 1.0
    assert report["summary"]["citation_complete_rate"] == 1.0
    assert report["cases"][0]["top_hit_match"] is True
    assert report["cases"][0]["retrieved_count"] == 1
