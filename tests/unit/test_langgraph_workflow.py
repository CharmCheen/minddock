"""Unit tests for the LangGraph retrieval workflow."""

from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.workflows.langgraph_pipeline import run_retrieval_workflow


class FakeSearchService:
    def retrieve(self, query: str, top_k: int, filters: RetrievalFilters | None = None) -> list[RetrievedChunk]:
        assert query == "storage"
        assert top_k == 2
        assert filters == RetrievalFilters(section="Storage")
        return [
            RetrievedChunk(
                text="MindDock stores chunks in Chroma.",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                title="doc",
                section="Storage",
                location="Storage",
                ref="doc > Storage",
                page=None,
                anchor=None,
                distance=0.2,
            )
        ]


def test_langgraph_retrieval_workflow_prepares_context_and_citations() -> None:
    result = run_retrieval_workflow(
        query="storage",
        top_k=2,
        filters=RetrievalFilters(section="Storage"),
        search_service=FakeSearchService(),
    )

    assert len(result.grounded_hits) == 1
    assert result.context.to_evidence_items()[0]["chunk_id"] == "c1"
    assert result.citations[0].ref == "doc > Storage"
    assert result.grouped_hits[0].doc_id == "d1"
