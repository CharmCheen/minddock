"""Tests for hybrid retrieval debug/diagnostic capabilities."""

from __future__ import annotations

from app.rag.hybrid_retrieval import (
    HybridRetrievalService,
    _rrf_fuse,
)
from app.rag.retrieval_models import RetrievedChunk


def _chunk(chunk_id: str, text: str, doc_id: str = "doc-a", source: str = "kb/a.md") -> RetrievedChunk:
    return RetrievedChunk(text=text, doc_id=doc_id, chunk_id=chunk_id, source=source)


class _FakeVectorStore:
    def __init__(self, chunks: list[RetrievedChunk], dense_hits: list[RetrievedChunk]) -> None:
        self._chunks_by_id = {c.chunk_id: c for c in chunks}
        self._dense_hits = dense_hits
        self._store = type("S", (), {"_collection": type("C", (), {"get": lambda self, include=None: {
            "documents": [c.text for c in chunks],
            "metadatas": [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "source": c.source} for c in chunks],
        }})()})()

    def count(self) -> int:
        return len(self._chunks_by_id)

    def search_by_text(self, query: str, top_k: int, filters=None):
        return self._dense_hits[:top_k]

    def get_chunks_by_ids(self, chunk_ids: list[str], filters=None):
        return [self._chunks_by_id[cid] for cid in chunk_ids if cid in self._chunks_by_id]


def test_rrf_fuse_preserves_both_list_contributions() -> None:
    """RRF fusion gives higher scores to items appearing in both lists."""
    # List A: items [0, 1, 2] ranked by position
    # List B: items [2, 0, 3] ranked by position
    # Item 2 appears in both (pos 2 in A, pos 0 in B) → should rank highest
    fused = _rrf_fuse(
        [
            [(0, 1.0), (1, 1.0), (2, 1.0)],
            [(2, 5.0), (0, 3.0), (3, 1.0)],
        ],
        limit=4,
        rrf_k=60,
    )
    fused_dict = {idx: score for idx, score in fused}
    # Item 2: 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226
    # Item 0: 1/(60+1) + 1/(60+2) = 0.01639 + 0.01613 = 0.03252
    # Item 0 and 2 should both score higher than items appearing in only one list
    assert fused_dict[0] > fused_dict[1]  # 0 in both, 1 only in A
    assert fused_dict[0] > fused_dict[3]  # 0 in both, 3 only in B
    assert fused_dict[2] > fused_dict[1]
    assert fused_dict[2] > fused_dict[3]


def test_rrf_same_doc_chunk_reordering_demonstrated() -> None:
    """Demonstrate that RRF can reorder chunks within the same document.

    When chunk_A is dense rank 1 and chunk_B is dense rank 3 but BM25 rank 1,
    RRF gives chunk_B a higher score because it appears in both lists.
    This is the root cause of hit@1 regression on search_retrieval_flow.
    """
    chunk_a = _chunk("doc:3", "expected chunk", doc_id="doc-x", source="rag.md")
    chunk_b = _chunk("doc:2", "other chunk from same doc", doc_id="doc-x", source="rag.md")
    chunk_c = _chunk("other:0", "different doc chunk", doc_id="doc-y", source="other.md")

    # Dense ranking: chunk_a at pos 0, chunk_c at pos 1, chunk_b at pos 2
    # BM25 ranking: chunk_b at pos 0, chunk_c at pos 1
    dense_list = [(0, 1.0), (1, 1.0), (2, 1.0)]
    bm25_list = [(2, 5.0), (1, 3.0)]  # chunk_b (pos 2) ranked first by BM25

    fused = _rrf_fuse([dense_list, bm25_list], limit=3, rrf_k=60)
    fused_dict = {idx: score for idx, score in fused}

    # chunk_b (idx=2) appears in both lists → gets boosted above chunk_a (idx=0)
    # chunk_a: 1/(60+1) = 0.01639 (dense only)
    # chunk_b: 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226 (both)
    assert fused_dict[2] > fused_dict[0], (
        "chunk_b (dense rank 3 + BM25 rank 1) should score higher than "
        "chunk_a (dense rank 1 only) due to dual-list boost"
    )

    # The top result is chunk_b (idx=2), not chunk_a (idx=0)
    assert fused[0][0] == 2


def test_hybrid_retrieve_same_doc_dense_order_preserved() -> None:
    """After RRF, chunks from the same document preserve dense rank order.

    Before the fix, RRF would promote doc:2 (BM25 rank 1) above doc:3 (dense rank 1)
    because doc:2 appeared in both lists. After the fix, same-doc chunks are sorted
    by dense rank, so doc:3 stays before doc:2.
    """
    chunk_a = _chunk("doc:3", "expected chunk text", doc_id="doc-x", source="rag.md")
    chunk_b = _chunk("doc:2", "other chunk same doc", doc_id="doc-x", source="rag.md")
    chunk_c = _chunk("other:0", "different doc", doc_id="doc-y", source="other.md")

    # Dense: doc:3 (pos 0), other:0 (pos 1), doc:2 (pos 2)
    # BM25 will find doc:2 first (term overlap), then doc:3
    store = _FakeVectorStore(
        chunks=[chunk_a, chunk_b, chunk_c],
        dense_hits=[chunk_a, chunk_c, chunk_b],
    )
    service = HybridRetrievalService(store, feature_flag=True, bm25_top_k=10)

    hits = service.retrieve("expected chunk", top_k=3)
    hit_ids = [h.chunk_id for h in hits]

    assert len(hits) == 3
    # doc:3 should come BEFORE doc:2 (dense rank preserved within same doc)
    idx_a = hit_ids.index("doc:3")
    idx_b = hit_ids.index("doc:2")
    assert idx_a < idx_b, (
        f"doc:3 (dense rank 0) should come before doc:2 (dense rank 2) "
        f"within the same document, but got positions {idx_a} and {idx_b}"
    )


def test_hybrid_metadata_preserved_through_fusion() -> None:
    """Hybrid retrieval preserves all metadata fields through RRF fusion."""
    chunk = _chunk("doc:0", "test text", doc_id="doc-x", source="kb/test.md")
    store = _FakeVectorStore(chunks=[chunk], dense_hits=[chunk])
    service = HybridRetrievalService(store, feature_flag=True)

    hits = service.retrieve("test", top_k=1)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.doc_id == "doc-x"
    assert hit.chunk_id == "doc:0"
    assert hit.source == "kb/test.md"
    assert hit.text == "test text"


def test_hybrid_fallback_when_bm25_empty() -> None:
    """When BM25 returns no results, hybrid falls back to dense-only."""
    chunk = _chunk("doc:0", "alpha beta", doc_id="doc-a", source="kb/a.md")
    store = _FakeVectorStore(chunks=[chunk], dense_hits=[chunk])
    service = HybridRetrievalService(store, feature_flag=True)

    # Empty BM25 index → falls back to dense
    hits = service.retrieve("alpha", top_k=1)
    assert len(hits) == 1
    assert hits[0].chunk_id == "doc:0"
