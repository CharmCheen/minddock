"""Regression tests for hybrid dense + BM25 retrieval fusion."""

import gc

from app.rag.hybrid_retrieval import (
    HybridRetrievalService,
    _INVALIDATION_CALLBACKS,
    _notify_invalidation,
    register_invalidation_callback,
)
from app.rag.retrieval_models import RetrievedChunk
from app.rag.vectorstore import LangChainChromaStore
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


class _FakeDeleteStore:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids
        self.deleted_where = None

    def get(self, where, include=None):  # noqa: ANN001, ARG002
        return {"ids": self._ids}

    def delete(self, where):  # noqa: ANN001
        self.deleted_where = where


class _FakeUpsertCollection:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def upsert(self, **payload) -> None:  # noqa: ANN003
        self.payload = payload


class _FakeUpsertStore:
    def __init__(self) -> None:
        self._collection = _FakeUpsertCollection()


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


# ---------------------------------------------------------------------------
# Regression: BM25 cache invalidation (Bug C)
# ---------------------------------------------------------------------------


def test_bm25_cache_invalidation_rebuilds_index() -> None:
    """After invalidate_cache(), the BM25 index should be rebuilt on next retrieval."""
    chunk_a = RetrievedChunk(
        text="original content about machine learning",
        doc_id="doc-a",
        chunk_id="chunk-a",
        source="kb/a.md",
        source_type="file",
        distance=0.1,
    )
    chunk_b = RetrievedChunk(
        text="new content about deep learning neural networks",
        doc_id="doc-b",
        chunk_id="chunk-b",
        source="kb/b.md",
        source_type="file",
        distance=0.2,
    )
    store = _FakeVectorStore(
        chunks=[chunk_a],
        dense_hits=[chunk_a],
    )
    service = HybridRetrievalService(
        vectorstore=store,
        feature_flag=True,
        bm25_top_k=10,
        rrf_k=60,
    )

    # First retrieval builds the index — only chunk_a exists
    hits1 = service.retrieve("machine learning", top_k=2)
    hit_ids_1 = {h.chunk_id for h in hits1}
    assert "chunk-a" in hit_ids_1
    assert "chunk-b" not in hit_ids_1
    assert service._built is True

    # Simulate adding a new document to the vectorstore
    store._chunks_by_id["chunk-b"] = chunk_b
    store._store._collection._chunks["chunk-b"] = chunk_b
    store._dense_hits = [chunk_a, chunk_b]

    # Without invalidation, BM25 index is stale — chunk_b not found by BM25
    service.invalidate_cache()
    assert service._built is False
    assert service._bm25_index is None

    # After invalidation, the rebuilt index should include chunk_b
    hits2 = service.retrieve("deep learning neural", top_k=2)
    hit_ids_2 = {h.chunk_id for h in hits2}
    assert "chunk-b" in hit_ids_2


def test_delete_document_notifies_bm25_invalidation_only_after_actual_delete(monkeypatch) -> None:
    """delete_document() should invalidate BM25 cache only when chunks are actually deleted."""
    invalidations: list[str] = []
    monkeypatch.setattr("app.rag.hybrid_retrieval._notify_invalidation", lambda: invalidations.append("invalidated"))

    store = LangChainChromaStore.__new__(LangChainChromaStore)
    backing_store = _FakeDeleteStore(ids=["chunk-b"])
    store._store = backing_store

    deleted = store.delete_document("doc-b")

    assert deleted == 1
    assert backing_store.deleted_where == {"doc_id": "doc-b"}
    assert invalidations == ["invalidated"]

    empty_store = LangChainChromaStore.__new__(LangChainChromaStore)
    empty_backing_store = _FakeDeleteStore(ids=[])
    empty_store._store = empty_backing_store

    deleted = empty_store.delete_document("doc-empty")

    assert deleted == 0
    assert empty_backing_store.deleted_where is None
    assert invalidations == ["invalidated"]


def test_upsert_notifies_bm25_invalidation(monkeypatch) -> None:
    invalidations: list[str] = []
    monkeypatch.setattr("app.rag.hybrid_retrieval._notify_invalidation", lambda: invalidations.append("invalidated"))

    store = LangChainChromaStore.__new__(LangChainChromaStore)
    backing_store = _FakeUpsertStore()
    store._store = backing_store

    store.upsert(
        ids=["chunk-a"],
        documents=["new content"],
        metadatas=[{"doc_id": "doc-a", "chunk_id": "chunk-a"}],
        embeddings=[[0.1, 0.2]],
    )

    assert backing_store._collection.payload is not None
    assert invalidations == ["invalidated"]


def test_bm25_invalidation_callbacks_are_deduped_and_weak() -> None:
    _INVALIDATION_CALLBACKS.clear()
    chunk = _chunk(
        text="hybrid retrieval cache lifecycle",
        doc_id="doc-a",
        chunk_id="chunk-a",
        source="kb/a.md",
        title="Doc A",
        section="Cache",
        page=1,
        marker="cache",
    )
    store = _FakeVectorStore(chunks=[chunk], dense_hits=[chunk])
    service = HybridRetrievalService(vectorstore=store, feature_flag=True)

    register_invalidation_callback(service.invalidate_cache)

    assert len(_INVALIDATION_CALLBACKS) == 1
    service.retrieve("cache lifecycle", top_k=1)
    assert service._built is True

    del service
    gc.collect()
    _notify_invalidation()

    assert _INVALIDATION_CALLBACKS == []
