"""Unit tests for reranking and compression."""

import pytest

from app.rag.postprocess import (
    HeuristicReranker,
    TrimmingCompressor,
    _get_metadata_bias,
    _AUTHOR_BIAS,
    _REFERENCE_BIAS,
    _ABSTRACT_BIAS,
)
from app.rag.retrieval_models import RetrievedChunk
from app.services.grounded_generation import build_citation


def _make_hit(
    *,
    chunk_id: str,
    text: str,
    section: str = "Introduction",
    block_type: str = "paragraph",
    semantic_type: str = "",
    distance: float = 0.1,
) -> RetrievedChunk:
    """Helper to build a RetrievedChunk with extra_metadata."""
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


# ---------------------------------------------------------------------------
# Metadata bias unit tests
# ---------------------------------------------------------------------------

class TestMetadataBias:
    def test_abstract_semantic_type_gets_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="Large Language Models have revolutionized artificial intelligence.",
            section="Abstract",
            block_type="paragraph",
            semantic_type="abstract",
        )
        bias = _get_metadata_bias(hit, "what are large language models")
        assert bias == _ABSTRACT_BIAS

    def test_author_block_type_gets_strong_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="John Smith, Jane Doe, and Wei Liu contributed equally.",
            section="Author Contributions",
            block_type="author",
        )
        bias = _get_metadata_bias(hit, "who wrote this paper")
        assert bias == _AUTHOR_BIAS

    def test_reference_block_type_gets_strong_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="[1] Smith, J. et al. (2024). Advances in AI. Journal of AI.",
            section="References",
            block_type="reference",
        )
        bias = _get_metadata_bias(hit, "what are the references")
        assert bias == _REFERENCE_BIAS

    def test_reference_section_in_section_title_gets_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="Gomez-Escalante, S., & Dudzik, B. (2023). Peeragogy in practice.",
            section="References",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "machine learning trends")
        assert bias == _REFERENCE_BIAS

    def test_author_section_in_section_title_gets_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="Aditi Singh, Department of Computer Science, Cleveland State University.",
            section="Authors",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "deep learning methods")
        assert bias == _AUTHOR_BIAS

    def test_chinese_author_section_gets_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="王睿 齐建鹏 陈亮",
            section="作者",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "边缘计算方法")
        assert bias == _AUTHOR_BIAS

    def test_chinese_references_section_gets_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="张伟, 李明. 人工智能综述[J]. 计算机学报, 2024.",
            section="参考文献",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "自然语言处理")
        assert bias == _REFERENCE_BIAS

    def test_body_paragraph_gets_zero_bias(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="Retrieval-Augmented Generation combines retrieval with language models.",
            section="Related Work",
            block_type="paragraph",
            semantic_type="",
        )
        bias = _get_metadata_bias(hit, "what is RAG")
        assert bias == 0.0

    def test_abstract_intent_bypasses_abstract_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="We present a comprehensive survey of agentic RAG systems.",
            section="Abstract",
            block_type="paragraph",
            semantic_type="abstract",
        )
        bias = _get_metadata_bias(hit, "what is the abstract of this paper")
        assert bias == 0.0

    def test_author_intent_bypasses_author_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="John Smith, Jane Doe, Wei Liu.",
            section="Authors",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "who are the authors")
        assert bias == 0.0, f"Expected 0 for explicit author query, got {bias}"

    def test_reference_intent_bypasses_reference_penalty(self) -> None:
        hit = _make_hit(
            chunk_id="c1",
            text="[1] Smith J. et al. (2024).",
            section="References",
            block_type="paragraph",
        )
        bias = _get_metadata_bias(hit, "what are the references")
        assert bias == 0.0, f"Expected 0 for explicit reference query, got {bias}"
        bias2 = _get_metadata_bias(hit, "list the references")
        assert bias2 == 0.0, f"Expected 0 for list references query, got {bias2}"

    def test_missing_extra_metadata_gets_zero_bias(self) -> None:
        hit = RetrievedChunk(
            text="Some content about neural networks.",
            doc_id="d1",
            chunk_id="c1",
            source="test.pdf",
            section="Methods",
            distance=0.1,
            # No extra_metadata set
        )
        bias = _get_metadata_bias(hit, "neural networks")
        assert bias == 0.0


# ---------------------------------------------------------------------------
# HeuristicReranker integration tests
# ---------------------------------------------------------------------------

class TestHeuristicRerankerMetadata:
    def test_author_hit_ranked_lower_for_general_query(self) -> None:
        """For a general RAG query, author blocks should be ranked lower than body."""
        reranker = HeuristicReranker()
        hits = [
            _make_hit(
                chunk_id="c_body",
                text="Retrieval-Augmented Generation combines retrieval with language models for better accuracy.",
                section="Related Work",
                block_type="paragraph",
                distance=0.05,
            ),
            _make_hit(
                chunk_id="c_author",
                text="John Smith, Jane Doe, Wei Liu — Department of Computer Science.",
                section="Authors",
                block_type="paragraph",
                distance=0.05,
            ),
        ]

        reranked = reranker.rerank("what is RAG", hits)
        body_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_body")
        author_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_author")
        assert body_rank < author_rank, "Body paragraph should rank higher than author block"

    def test_abstract_hit_ranked_lower_for_general_query(self) -> None:
        """For a general query, abstract body should be ranked lower than body paragraphs."""
        reranker = HeuristicReranker()
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
                text="We survey recent advances in edge intelligence, covering协同推理, machine learning, and IoT.",
                section="Abstract",
                block_type="paragraph",
                semantic_type="abstract",
                distance=0.05,
            ),
        ]

        reranked = reranker.rerank("edge intelligence techniques", hits)
        body_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_body")
        abstract_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_abstract")
        assert body_rank < abstract_rank, "Body paragraph should rank higher than abstract"

    def test_reference_hit_ranked_lower_for_general_query(self) -> None:
        """For a general query, reference blocks should be ranked lower than body."""
        reranker = HeuristicReranker()
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
                text="[42] Wang, H. et al. Deep learning for edge computing. IEEE Trans. 2023.",
                section="References",
                block_type="paragraph",
                distance=0.05,
            ),
        ]

        reranked = reranker.rerank("what accuracy does the method achieve", hits)
        body_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_body")
        ref_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_ref")
        assert body_rank < ref_rank, "Body paragraph should rank higher than reference"

    def test_abstract_query_allows_abstract_in_top_positions(self) -> None:
        """For an abstract query, abstract blocks should not be penalized."""
        reranker = HeuristicReranker()
        hits = [
            _make_hit(
                chunk_id="c_body",
                text="Experimental results show 95% accuracy on the standard benchmark.",
                section="Results",
                block_type="paragraph",
                distance=0.1,
            ),
            _make_hit(
                chunk_id="c_abstract",
                text="We present a survey of agentic RAG covering architecture, evaluation, and future directions.",
                section="Abstract",
                block_type="paragraph",
                semantic_type="abstract",
                distance=0.05,
            ),
        ]

        reranked = reranker.rerank("what is the abstract of this survey", hits)
        # The penalty is bypassed for abstract queries; abstract should be in top 2
        abstract_rank = next(i for i, h in enumerate(reranked) if h.chunk_id == "c_abstract")
        assert abstract_rank <= 1, "Abstract should be in top 2 when query asks for abstract"

    def test_author_query_penalty_removed_for_author_section(self) -> None:
        """When query is about authors, the author section penalty is removed."""
        reranker = HeuristicReranker()
        hits = [
            _make_hit(
                chunk_id="c_body",
                text="The methodology uses a transformer-based encoder with retrieval augmentation.",
                section="Methods",
                block_type="paragraph",
                distance=0.1,
            ),
            _make_hit(
                chunk_id="c_author",
                text="Aditi Singh, Department of Computer Science, Cleveland State University.",
                section="Authors",
                block_type="paragraph",
                distance=0.1,
            ),
        ]

        reranked = reranker.rerank("who are the authors", hits)
        # Penalty should be bypassed (bias=0) for author query
        author_hit = next(h for h in reranked if h.chunk_id == "c_author")
        body_hit = next(h for h in reranked if h.chunk_id == "c_body")
        # When penalty is bypassed, score difference should be smaller than with penalty
        # (the penalty is -0.15, so without it author should be closer to body)
        score_diff = abs(author_hit.rerank_score - body_hit.rerank_score)
        assert score_diff < 0.2, "Without penalty, author and body scores should be close"

    def test_reference_query_penalty_removed_for_reference_section(self) -> None:
        """When query is about references, the reference section penalty is removed."""
        reranker = HeuristicReranker()
        hits = [
            _make_hit(
                chunk_id="c_body",
                text="The conclusion outlines five promising research directions.",
                section="Conclusion",
                block_type="paragraph",
                distance=0.1,
            ),
            _make_hit(
                chunk_id="c_ref",
                text="[1] Chen, L. et al. (2024). Agentic RAG: A comprehensive survey. arXiv.",
                section="References",
                block_type="paragraph",
                distance=0.1,
            ),
        ]

        reranked = reranker.rerank("what are the references", hits)
        ref_hit = next(h for h in reranked if h.chunk_id == "c_ref")
        body_hit = next(h for h in reranked if h.chunk_id == "c_body")
        # Without penalty, reference and body should have closer scores
        score_diff = abs(ref_hit.rerank_score - body_hit.rerank_score)
        assert score_diff < 0.2, "Without penalty, reference and body scores should be close"


def test_heuristic_reranker_changes_hit_order() -> None:
    reranker = HeuristicReranker()
    hits = [
        RetrievedChunk(
            text="General notes about unrelated UI polish.",
            doc_id="d1",
            chunk_id="c1",
            source="ui.md",
            title="UI",
            section="Design",
            location="Design",
            ref="UI > Design",
            distance=0.05,
        ),
        RetrievedChunk(
            text="MindDock stores document chunks and metadata in local Chroma storage.",
            doc_id="d2",
            chunk_id="c2",
            source="storage.md",
            title="Storage",
            section="Persistence",
            location="Persistence",
            ref="Storage > Persistence",
            distance=0.4,
        ),
    ]

    reranked = reranker.rerank("where are chunks stored", hits)

    assert reranked[0].chunk_id == "c2"
    assert reranked[0].rerank_score >= reranked[1].rerank_score


def test_trimming_compressor_shortens_text_and_preserves_citation_text() -> None:
    compressor = TrimmingCompressor()
    hits = [
        RetrievedChunk(
            text=(
                "MindDock stores chunks in Chroma. "
                "This sentence is relevant to storage. "
                "Unrelated sentence about weather and coffee."
            ),
            doc_id="d1",
            chunk_id="c1",
            source="storage.md",
            title="Storage",
            section="Persistence",
            location="Persistence",
            ref="Storage > Persistence",
            distance=0.2,
        )
    ] * 6

    compressed = compressor.compress("where are chunks stored", hits)
    citation = build_citation(compressed[0])

    assert len(compressed) == 4
    assert compressed[0].compression_applied is True
    assert len(compressed[0].text) < len(hits[0].text)
    assert compressed[0].original_text == hits[0].text
    assert citation.snippet.startswith("MindDock stores chunks in Chroma.")
