"""Regression tests for hybrid dense + BM25 retrieval fusion."""

from app.rag.hybrid_retrieval import HybridRetrievalService
from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation, build_evidence


class _FakeCollection:
    def __init__(self, chunks: dict[str, RetrievedChunk]) -> None:
        self._chunks = chunks

    def get(self, include=None):  # noqa: ANN001
        return {
            "documents": [chunk.text for chunk in self._chunks.values()],
            "metadatas": [
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "source_type": chunk.source_type,
                    "title": chunk.title,
                    "section": chunk.section,
                    "location": chunk.location,
                    "page": chunk.page,
                    **chunk.extra_metadata,
                }
                for chunk in self._chunks.values()
            ],
        }


class _FakeChromaStore:
    def __init__(self, chunks: dict[str, RetrievedChunk]) -> None:
        self._collection = _FakeCollection(chunks)


class _FakeVectorStore:
    def __init__(
        self,
        *,
        chunks: list[RetrievedChunk],
        dense_hits: list[RetrievedChunk],
    ) -> None:
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._dense_hits = dense_hits
        self._store = _FakeChromaStore(self._chunks_by_id)
        self.requested_chunk_ids: list[str] = []

    def count(self) -> int:
        return len(self._chunks_by_id)

    def search_by_text(self, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:  # noqa: ANN001, ARG002
        return self._dense_hits[:top_k]

    def get_chunks_by_ids(self, chunk_ids: list[str], filters=None) -> list[RetrievedChunk]:  # noqa: ANN001, ARG002
        self.requested_chunk_ids.extend(chunk_ids)
        return [
            self._chunks_by_id[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self._chunks_by_id
        ]


def _chunk(
    *,
    text: str,
    doc_id: str,
    chunk_id: str,
    source: str,
    title: str,
    section: str,
    page: int,
    marker: str,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        doc_id=doc_id,
        chunk_id=chunk_id,
        source=source,
        source_type="file",
        title=title,
        section=section,
        location=section,
        page=page,
        extra_metadata={"marker": marker, "source_path": source},
    )


def test_hybrid_retrieval_fetches_complete_chunks_for_bm25_only_hits() -> None:
    dense_chunk = _chunk(
        text="dense alpha text",
        doc_id="doc-a",
        chunk_id="chunk-a",
        source="kb/a.md",
        title="Dense A",
        section="Dense",
        page=1,
        marker="dense-a",
    )
    lexical_b = _chunk(
        text="unique lexical beta evidence",
        doc_id="doc-b",
        chunk_id="chunk-b",
        source="kb/b.md",
        title="Lexical B",
        section="Beta",
        page=2,
        marker="lexical-b",
    )
    lexical_c = _chunk(
        text="unique lexical gamma evidence",
        doc_id="doc-c",
        chunk_id="chunk-c",
        source="kb/c.md",
        title="Lexical C",
        section="Gamma",
        page=3,
        marker="lexical-c",
    )
    vectorstore = _FakeVectorStore(
        chunks=[dense_chunk, lexical_b, lexical_c],
        dense_hits=[dense_chunk],
    )
    service = HybridRetrievalService(
        vectorstore,
        feature_flag=True,
        bm25_top_k=3,
    )

    hits = service.retrieve("unique lexical gamma beta", top_k=3)
    hits_by_id = {hit.chunk_id: hit for hit in hits}

    assert {"chunk-b", "chunk-c"}.issubset(hits_by_id)
    assert vectorstore.requested_chunk_ids == ["chunk-b", "chunk-c"]

    assert hits_by_id["chunk-b"].doc_id == "doc-b"
    assert hits_by_id["chunk-b"].source == "kb/b.md"
    assert hits_by_id["chunk-b"].text == "unique lexical beta evidence"
    assert hits_by_id["chunk-b"].extra_metadata["marker"] == "lexical-b"

    assert hits_by_id["chunk-c"].doc_id == "doc-c"
    assert hits_by_id["chunk-c"].source == "kb/c.md"
    assert hits_by_id["chunk-c"].text == "unique lexical gamma evidence"
    assert hits_by_id["chunk-c"].extra_metadata["marker"] == "lexical-c"

    assert hits_by_id["chunk-b"].source != dense_chunk.source
    assert hits_by_id["chunk-b"].text != dense_chunk.text
    assert hits_by_id["chunk-c"].source != dense_chunk.source
    assert hits_by_id["chunk-c"].text != dense_chunk.text


def test_hybrid_retrieval_bm25_only_metadata_feeds_citation_and_evidence() -> None:
    dense_chunk = _chunk(
        text="dense alpha text",
        doc_id="doc-a",
        chunk_id="chunk-a",
        source="kb/a.md",
        title="Dense A",
        section="Dense",
        page=1,
        marker="dense-a",
    )
    lexical_chunk = _chunk(
        text="citation grounded lexical evidence",
        doc_id="doc-b",
        chunk_id="chunk-b",
        source="kb/b.md",
        title="Lexical B",
        section="Evidence",
        page=5,
        marker="lexical-b",
    )
    vectorstore = _FakeVectorStore(
        chunks=[dense_chunk, lexical_chunk],
        dense_hits=[dense_chunk],
    )
    service = HybridRetrievalService(
        vectorstore,
        feature_flag=True,
        bm25_top_k=2,
    )

    hits = service.retrieve("citation grounded lexical", top_k=2)
    lexical_hit = next(hit for hit in hits if hit.chunk_id == "chunk-b")
    citation = build_citation(lexical_hit)
    evidence = build_evidence(lexical_hit)

    assert citation.doc_id == "doc-b"
    assert citation.chunk_id == "chunk-b"
    assert citation.source == "kb/b.md"
    assert citation.page == 5
    assert "citation grounded lexical evidence" in citation.snippet

    assert evidence.doc_id == "doc-b"
    assert evidence.chunk_id == "chunk-b"
    assert evidence.source == "kb/b.md"
    assert evidence.snippet == "citation grounded lexical evidence"
