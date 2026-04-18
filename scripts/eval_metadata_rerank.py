# -*- coding: utf-8 -*-
"""Minimal before/after evaluation of metadata-aware reranking.

Demonstrates that AUTHOR / ABSTRACT / REFERENCE sections are down-ranked
for general queries, while intent queries (explicitly asking about these
sections) bypass the penalty.
"""
from __future__ import annotations

from app.rag.postprocess import (
    HeuristicReranker,
    _get_metadata_bias,
    _AUTHOR_BIAS,
    _REFERENCE_BIAS,
    _ABSTRACT_BIAS,
)
from app.rag.retrieval_models import RetrievedChunk


def _make_hit(
    *,
    chunk_id: str,
    text: str,
    section: str = "Introduction",
    block_type: str = "paragraph",
    semantic_type: str = "",
    distance: float = 0.1,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        doc_id="d1",
        chunk_id=chunk_id,
        source="test.pdf",
        title="Test Paper",
        section=section,
        location="page 1",
        ref="Test > Introduction",
        distance=distance,
        extra_metadata={
            "block_type": block_type,
            "semantic_type": semantic_type,
        },
    )


def _run_query(query: str, hits: list[RetrievedChunk]) -> list[tuple[str, float]]:
    reranker = HeuristicReranker()
    reranked = reranker.rerank(query, hits)
    return [(h.chunk_id, h.rerank_score) for h in reranked]


def main():
    print("=" * 70)
    print("METADATA-AWARE RERANK EVALUATION")
    print("=" * 70)
    print()

    # ── Test 1: General query: AUTHOR blocks penalized ──────────────────────
    print("TEST 1: General query — AUTHOR block should be ranked lower")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="Retrieval-Augmented Generation (RAG) combines retrieval with language models.",
            section="Related Work",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_author",
            text="Aditi Singh, Department of Computer Science, Cleveland State University.",
            section="Authors",
            block_type="paragraph",
            distance=0.05,
        ),
    ]
    results = _run_query("what is RAG", hits)
    for chunk_id, score in results:
        print(f"  {chunk_id:12s}  score={score:.4f}")
    body_rank = next(i for i, (c, _) in enumerate(results) if c == "c_body")
    author_rank = next(i for i, (c, _) in enumerate(results) if c == "c_author")
    verdict = "PASS" if body_rank < author_rank else "FAIL"
    print(f"  → Body rank {body_rank}, Author rank {author_rank}  [{verdict}]")
    print()

    # ── Test 2: General query: REFERENCE blocks penalized ────────────────────
    print("TEST 2: General query — REFERENCE block should be ranked lower")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="The proposed method achieves 95% accuracy on standard benchmarks.",
            section="Experiments",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_ref",
            text="[42] Wang H. et al. Deep learning for edge computing. IEEE Trans. 2023.",
            section="References",
            block_type="paragraph",
            distance=0.05,
        ),
    ]
    results = _run_query("what accuracy does the method achieve", hits)
    for chunk_id, score in results:
        print(f"  {chunk_id:12s}  score={score:.4f}")
    body_rank = next(i for i, (c, _) in enumerate(results) if c == "c_body")
    ref_rank = next(i for i, (c, _) in enumerate(results) if c == "c_ref")
    verdict = "PASS" if body_rank < ref_rank else "FAIL"
    print(f"  → Body rank {body_rank}, Reference rank {ref_rank}  [{verdict}]")
    print()

    # ── Test 3: General query: ABSTRACT semantic_type penalized ─────────────
    print("TEST 3: General query — ABSTRACT semantic_type should be ranked lower")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="Edge intelligence enables real-time inference at the network edge.",
            section="Introduction",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_abstract",
            text="We survey recent advances in edge intelligence, covering machine learning and IoT.",
            section="Abstract",
            block_type="paragraph",
            semantic_type="abstract",
            distance=0.05,
        ),
    ]
    results = _run_query("edge intelligence techniques", hits)
    for chunk_id, score in results:
        print(f"  {chunk_id:12s}  score={score:.4f}")
    body_rank = next(i for i, (c, _) in enumerate(results) if c == "c_body")
    abstract_rank = next(i for i, (c, _) in enumerate(results) if c == "c_abstract")
    verdict = "PASS" if body_rank < abstract_rank else "FAIL"
    print(f"  → Body rank {body_rank}, Abstract rank {abstract_rank}  [{verdict}]")
    print()

    # ── Test 4: Intent query: ABSTRACT penalty bypassed ───────────────────
    print("TEST 4: Abstract query — ABSTRACT penalty should be bypassed")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="Experimental results show 95% accuracy on the standard benchmark.",
            section="Results",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_abstract",
            text="We present a survey of agentic RAG covering architecture and future directions.",
            section="Abstract",
            block_type="paragraph",
            semantic_type="abstract",
            distance=0.05,
        ),
    ]
    abstract_bias = _get_metadata_bias(hits[1], "what is the abstract of this paper")
    body_bias = _get_metadata_bias(hits[0], "what is the abstract of this paper")
    verdict = "PASS" if abstract_bias == 0.0 and body_bias == 0.0 else "FAIL"
    print(f"  → Abstract bias = {abstract_bias} (expected 0), Body bias = {body_bias} (expected 0)  [{verdict}]")
    print()

    # ── Test 5: Intent query: AUTHOR penalty bypassed ───────────────────────
    print("TEST 5: Author query — AUTHOR penalty should be bypassed")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="The methodology uses a transformer-based encoder with retrieval augmentation.",
            section="Methods",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_author",
            text="Aditi Singh, Department of Computer Science, Cleveland State University.",
            section="Authors",
            block_type="paragraph",
            distance=0.05,
        ),
    ]
    results = _run_query("who are the authors", hits)
    for chunk_id, score in results:
        print(f"  {chunk_id:12s}  score={score:.4f}")
    author_bias = _get_metadata_bias(hits[1], "who are the authors")
    verdict = "PASS" if author_bias == 0.0 else "FAIL"
    print(f"  → Author bias = {author_bias} (expected 0)  [{verdict}]")
    print()

    # ── Test 6: Intent query: REFERENCE penalty bypassed ──────────────────
    print("TEST 6: Reference query — REFERENCE penalty should be bypassed")
    print("-" * 70)
    hits = [
        _make_hit(
            chunk_id="c_body",
            text="The conclusion outlines five promising research directions.",
            section="Conclusion",
            block_type="paragraph",
            distance=0.05,
        ),
        _make_hit(
            chunk_id="c_ref",
            text="[1] Chen L. et al. (2024). Agentic RAG: A survey. arXiv.",
            section="References",
            block_type="paragraph",
            distance=0.05,
        ),
    ]
    ref_bias = _get_metadata_bias(hits[1], "what are the references")
    verdict = "PASS" if ref_bias == 0.0 else "FAIL"
    print(f"  → Reference bias = {ref_bias} (expected 0)  [{verdict}]")
    print()

    # ── Summary ────────────────────────────────────────────────────────────
    print("=" * 70)
    print("Bias constants used:")
    print(f"  AUTHOR_BIAS      = {_AUTHOR_BIAS}")
    print(f"  REFERENCE_BIAS  = {_REFERENCE_BIAS}")
    print(f"  ABSTRACT_BIAS   = {_ABSTRACT_BIAS}")
    print("=" * 70)


if __name__ == "__main__":
    main()
