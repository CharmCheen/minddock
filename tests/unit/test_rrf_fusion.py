"""Tests for RRF fusion behavior and same-document ranking stability."""

from __future__ import annotations

from app.rag.hybrid_retrieval import _rrf_fuse


def test_rrf_fuse_basic_ranking() -> None:
    """Items appearing in both lists get higher RRF scores."""
    list_a = [(0, 1.0), (1, 1.0), (2, 1.0)]
    list_b = [(1, 5.0), (3, 3.0)]

    fused = _rrf_fuse([list_a, list_b], limit=4, rrf_k=60)
    fused_dict = {idx: score for idx, score in fused}

    # Item 1 appears in both → highest score
    assert fused[0][0] == 1
    # Item 0 and 3 each appear in one list
    assert fused_dict[1] > fused_dict[0]
    assert fused_dict[1] > fused_dict[3]


def test_rrf_fuse_same_position_different_lists() -> None:
    """When two items have similar RRF scores, the tie is broken by total score."""
    # Item 0: pos 0 in A only → 1/61
    # Item 1: pos 1 in A, pos 1 in B → 1/61 + 1/61 = 2/61
    list_a = [(0, 1.0), (1, 1.0)]
    list_b = [(1, 1.0)]

    fused = _rrf_fuse([list_a, list_b], limit=2, rrf_k=60)
    assert fused[0][0] == 1  # Item 1 wins (both lists)


def test_rrf_fuse_preserves_order_for_dense_only_items() -> None:
    """Items only in the dense list maintain their relative order."""
    # 5 items only in dense, ranked 0-4
    dense = [(i, 1.0) for i in range(5)]
    # BM25 returns items 10-14 (completely different set)
    bm25 = [(10 + i, 1.0) for i in range(5)]

    fused = _rrf_fuse([dense, bm25], limit=10, rrf_k=60)

    # Dense-only items should maintain relative order
    dense_positions = [idx for idx, _ in fused if idx < 5]
    assert dense_positions == [0, 1, 2, 3, 4]


def test_rrf_fuse_bm25_only_items_ranked_after_dual_items() -> None:
    """Items only in BM25 should rank below items in both lists."""
    dense = [(0, 1.0), (1, 1.0)]
    bm25 = [(1, 5.0), (2, 3.0)]  # Item 1 in both, item 2 BM25 only

    fused = _rrf_fuse([dense, bm25], limit=3, rrf_k=60)
    fused_dict = {idx: score for idx, score in fused}

    # Item 1 (both lists) > item 0 (dense only) > item 2 (BM25 only)
    assert fused_dict[1] > fused_dict[0]
    assert fused_dict[0] > fused_dict[2]


def test_rrf_fuse_higher_bm25_rank_beats_lower_dense_rank() -> None:
    """A BM25 rank-1 item can beat a dense rank-1 item if the dense item isn't in BM25.

    This is the core mechanism causing same-document chunk reordering.
    """
    # Item 0: dense rank 1 only
    # Item 1: dense rank 3 + BM25 rank 1
    dense = [(0, 1.0), (2, 1.0), (1, 1.0)]
    bm25 = [(1, 5.0), (3, 3.0)]

    fused = _rrf_fuse([dense, bm25], limit=4, rrf_k=60)
    fused_dict = {idx: score for idx, score in fused}

    # Item 1: 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226
    # Item 0: 1/(60+1) = 0.01639
    assert fused_dict[1] > fused_dict[0], (
        "BM25 rank 1 + dense rank 3 should beat dense rank 1 only"
    )


def test_rrf_fuse_limit_respects_output_size() -> None:
    """RRF fusion respects the limit parameter."""
    dense = [(i, 1.0) for i in range(10)]
    bm25 = [(i, 1.0) for i in range(10)]

    fused = _rrf_fuse([dense, bm25], limit=3, rrf_k=60)
    assert len(fused) == 3


def test_rrf_fuse_empty_lists() -> None:
    """RRF fusion handles empty input lists."""
    assert _rrf_fuse([], limit=5) == []
    assert _rrf_fuse([[], []], limit=5) == []


def test_rrf_fuse_rrf_k_affects_score_distribution() -> None:
    """Lower rrf_k gives more weight to top-ranked items, increasing absolute scores."""
    dense = [(0, 1.0), (1, 1.0)]
    bm25 = [(1, 1.0)]

    fused_low_k = _rrf_fuse([dense, bm25], limit=2, rrf_k=10)
    fused_high_k = _rrf_fuse([dense, bm25], limit=2, rrf_k=120)

    dict_low = {idx: score for idx, score in fused_low_k}
    dict_high = {idx: score for idx, score in fused_high_k}

    # With lower rrf_k, all absolute scores are higher
    assert dict_low[0] > dict_high[0]
    assert dict_low[1] > dict_high[1]
