"""Hybrid retrieval: dense (Chroma) + BM25 lexical + RRF fusion."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from threading import Lock
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.rag.retrieval_models import RetrievedChunk

if TYPE_CHECKING:
    from app.rag.vectorstore import LangChainChromaStore

logger = logging.getLogger(__name__)

# Tokenization patterns — mirrors postprocess.py
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 indexing.

    Chinese text: uses jieba word segmentation.
    English text: extracts alphanumeric tokens.
    """
    if _HAS_CJK_RE.search(text):
        try:
            import jieba
            return [token.lower() for token in jieba.cut(text) if token.strip()]
        except ImportError:
            return [c.lower() for c in text.split() if c.strip()]
    return [token.lower() for token in _WORD_RE.findall(text)]


def _build_lexical_index(texts: list[str]) -> dict:
    """Build an in-memory BM25 index from a list of texts.

    Returns a dict with doc_freq, doc_term_freqs, doc_lengths, avg_doc_len, num_docs.
    """
    doc_freq: Counter = Counter()
    doc_term_freqs: list[Counter] = []
    doc_lengths: list[int] = []

    for text in texts:
        terms = _tokenize(text)
        term_freq = Counter(terms)
        doc_term_freqs.append(term_freq)
        doc_lengths.append(sum(term_freq.values()) or 1)
        for term in term_freq:
            doc_freq[term] += 1

    avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0
    return {
        "doc_freq": doc_freq,
        "doc_term_freqs": doc_term_freqs,
        "doc_lengths": doc_lengths,
        "avg_doc_len": avg_doc_len,
        "num_docs": len(texts),
    }


def _bm25_score(query: str, text: str, index: dict, k1: float = 1.2, b: float = 0.75) -> float:
    """Compute BM25 score for a single (query, text) pair."""
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0

    term_freq: Counter = index["doc_term_freqs"][text] if isinstance(text, int) else Counter()
    if not isinstance(term_freq, Counter):
        term_freq = Counter(_tokenize(text))

    doc_len = sum(term_freq.values())
    num_docs = max(index.get("num_docs", 0), 1)
    avg_doc_len = max(index.get("avg_doc_len", 1.0), 1.0)

    score = 0.0
    for term in query_terms:
        tf = term_freq.get(term, 0)
        if tf <= 0:
            continue
        df = index["doc_freq"].get(term, 0)
        idf = math.log(1 + (num_docs - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf * (tf * (k1 + 1) / max(denom, 1e-8))
    return score


def _rrf_fuse(rank_lists: list[list[tuple[int, float]]], limit: int, rrf_k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over multiple ranked lists."""
    fused: dict[int, float] = {}
    for ranked in rank_lists:
        for rank, (idx, _) in enumerate(ranked, start=1):
            fused[idx] = fused.get(idx, 0.0) + (1.0 / (rrf_k + rank))
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]


class BM25Index:
    """In-memory BM25 index built from a list of (chunk_id, text) pairs."""

    def __init__(self, index: dict, chunk_ids: list[str]) -> None:
        self._index = index
        self._chunk_ids = chunk_ids
        self._id_to_pos = {cid: i for i, cid in enumerate(chunk_ids)}

    @classmethod
    def from_chunks(cls, chunks: list[tuple[str, str]]) -> "BM25Index":
        """Build BM25 index from a list of (chunk_id, text) pairs."""
        chunk_ids = [c[0] for c in chunks]
        texts = [c[1] for c in chunks]
        index = _build_lexical_index(texts)
        logger.info("BM25 index built: num_docs=%d", len(chunk_ids))
        return cls(index, chunk_ids)

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Return top_k (chunk_index, score) sorted by BM25 score descending."""
        scores = []
        for idx, term_freq in enumerate(self._index["doc_term_freqs"]):
            num_docs = max(self._index.get("num_docs", 0), 1)
            avg_doc_len = max(self._index.get("avg_doc_len", 1.0), 1.0)
            k1, b = 1.2, 0.75
            doc_len = sum(term_freq.values())

            query_terms = _tokenize(query)
            score = 0.0
            for term in query_terms:
                tf = term_freq.get(term, 0)
                if tf <= 0:
                    continue
                df = self._index["doc_freq"].get(term, 0)
                idf = math.log(1 + (num_docs - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
                score += idf * (tf * (k1 + 1) / max(denom, 1e-8))
            scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_chunk_id(self, pos: int) -> str:
        return self._chunk_ids[pos]


_BUILD_LOCK = Lock()


class HybridRetrievalService:
    """Hybrid retrieval: dense (Chroma cosine) + BM25 lexical + RRF fusion.

    BM25 index is lazily built on first retrieval request by scanning all
    chunks currently stored in Chroma. Subsequent requests reuse the cached
    index. Set `hybrid_retrieval_enabled=False` (default) to use pure dense.
    """

    def __init__(
        self,
        vectorstore: "LangChainChromaStore",
        feature_flag: bool = False,
        bm25_top_k: int = 50,
        rrf_k: int = 60,
    ) -> None:
        self._vectorstore = vectorstore
        self._enabled = feature_flag
        self._bm25_top_k = bm25_top_k
        self._rrf_k = rrf_k
        self._bm25_index: BM25Index | None = None
        self._built = False

    def _ensure_bm25_ready(self) -> None:
        """Lazily build BM25 index from Chroma's current content.

        Thread-safe via _BUILD_LOCK: only one thread builds, others wait.
        """
        if self._built:
            return
        with _BUILD_LOCK:
            if self._built:
                return
            logger.info("Building BM25 index from Chroma (lazy, one-time)...")
            chunks = self._scan_all_chunks()
            if chunks:
                self._bm25_index = BM25Index.from_chunks(chunks)
                logger.info("BM25 index ready: %d chunks", len(chunks))
            else:
                logger.warning("No chunks found in Chroma for BM25 indexing")
            self._built = True

    def _scan_all_chunks(self) -> list[tuple[str, str]]:
        """Scan all chunks from Chroma and return (chunk_id, text) pairs."""
        from app.rag.retrieval_models import RetrievedChunk

        all_chunks: list[tuple[str, str]] = []
        total = self._vectorstore.count()
        if total == 0:
            return []

        # Chroma doesn't expose a "get all" API directly, but we can use
        # query with a dummy vector to get all documents. Instead, use
        # the internal _collection.get() with no filter.
        result = self._vectorstore._store._collection.get(
            include=["documents", "metadatas"]
        )
        documents: list[str] = result.get("documents") or []
        metadatas: list[list[dict]] = result.get("metadatas") or []

        for doc, meta in zip(documents, metadatas, strict=True):
            chunk_id = str(meta.get("chunk_id", "") if isinstance(meta, dict) else "")
            if chunk_id and doc:
                all_chunks.append((chunk_id, doc))

        logger.info("Scanned %d chunks from Chroma for BM25 index", len(all_chunks))
        return all_chunks

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters=None,
    ) -> list[RetrievedChunk]:
        """Execute hybrid retrieval and return normalized RetrievedChunks."""
        if not self._enabled:
            return self._vectorstore.search_by_text(query=query, top_k=top_k, filters=filters)

        self._ensure_bm25_ready()
        if self._bm25_index is None:
            logger.warning("BM25 index unavailable, falling back to dense-only")
            return self._vectorstore.search_by_text(query=query, top_k=top_k, filters=filters)

        settings = get_settings()
        dense_top_k = top_k
        max_lexical = min(self._bm25_top_k, len(self._bm25_index._chunk_ids))

        # Dense retrieval: returns hits in cosine-similarity order
        dense_hits = self._vectorstore.search_by_text(
            query=query, top_k=dense_top_k, filters=filters
        )

        # BM25 retrieval: (bm25_internal_pos, score) in BM25 score order
        bm25_results = self._bm25_index.search(query, max_lexical)

        # Build position-in-dense for each chunk_id; chunks not in dense get None
        dense_pos_map: dict[str, int] = {
            hit.chunk_id: pos for pos, hit in enumerate(dense_hits)
        }
        n = len(dense_hits)

        # RRF input: [(position_in_dense, 1.0)] for all dense hits
        #             [(bm25_position_in_lexical, bm25_score)] for all BM25 hits
        # Key insight: position in dense list = dense rank (1-based)
        #             position in bm25_results = bm25 rank (1-based)
        # Both indexed by same chunk_ids for chunks that appear in both lists.
        rrf_input: list[list[tuple[int, float]]] = []

        # Dense ranked: position in dense_hits list is the rank
        dense_rrf: list[tuple[int, float]] = [
            (pos, 1.0) for pos in range(n)
        ]
        rrf_input.append(dense_rrf)

        # BM25 ranked: bm25_results[i] = (bm25_internal_pos, score)
        # Map bm25_chunk_id -> its position in dense list
        # (uses chunk_id from bm25_index to cross-reference with dense)
        lexical_rrf: list[tuple[int, float]] = []
        for bm25_pos, bm25_score in bm25_results:
            bm25_chunk_id = self._bm25_index.get_chunk_id(bm25_pos)
            pos = dense_pos_map.get(bm25_chunk_id, n + bm25_pos)
            lexical_rrf.append((pos, bm25_score))
        rrf_input.append(lexical_rrf)

        fused = _rrf_fuse(rrf_input, top_k, rrf_k=self._rrf_k)

        # Reconstruct result in RRF order
        result: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        for rank_pos, _ in fused:
            if rank_pos < n:
                hit = dense_hits[rank_pos]
            else:
                # Chunk only in BM25 (not in dense top-k): look up by bm25_internal_pos
                bm25_idx = rank_pos - n
                if bm25_idx < len(bm25_results):
                    bm25_pos, _ = bm25_results[bm25_idx]
                    bm25_chunk_id = self._bm25_index.get_chunk_id(bm25_pos)
                    if result:
                        hit = result[0].with_updates(chunk_id=bm25_chunk_id)
                    else:
                        hit = dense_hits[0].with_updates(chunk_id=bm25_chunk_id)
                else:
                    continue
            if hit.chunk_id not in seen_ids:
                result.append(hit.with_updates(retrieval_rank=len(result) + 1))
                seen_ids.add(hit.chunk_id)

        # If RRF gave fewer than top_k, fill from dense
        for hit in dense_hits:
            if hit.chunk_id not in seen_ids and len(result) < top_k:
                result.append(hit.with_updates(retrieval_rank=len(result) + 1))
                seen_ids.add(hit.chunk_id)

        logger.debug(
            "Hybrid retrieval executed: query=%s top_k=%d dense=%d lexical=%d fused=%d",
            query[:40], top_k, len(dense_hits), len(bm25_results), len(result)
        )
        return result


def get_hybrid_retrieval_service(
    vectorstore,
    feature_flag: bool | None = None,
    bm25_top_k: int | None = None,
    rrf_k: int | None = None,
) -> HybridRetrievalService:
    """Factory: return HybridRetrievalService with settings from config or overrides."""
    if feature_flag is None:
        feature_flag = get_settings().hybrid_retrieval_enabled
    if bm25_top_k is None:
        bm25_top_k = get_settings().bm25_top_k
    if rrf_k is None:
        rrf_k = get_settings().rrf_k
    return HybridRetrievalService(
        vectorstore=vectorstore,
        feature_flag=feature_flag,
        bm25_top_k=bm25_top_k,
        rrf_k=rrf_k,
    )
